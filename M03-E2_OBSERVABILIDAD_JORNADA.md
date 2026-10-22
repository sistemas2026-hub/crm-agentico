# M03-E2 — Observabilidad y ordenamiento determinista de la jornada

**Fecha:** 2026-09-18
**Estado:** **[VALIDADO]** — 0 decisiones empresariales tomadas.

---

## Resumen

```
Archivos creados:      1        Archivos modificados:   5
Migraciones:           0        ← "No changes detected"
Modelos:               0        Roles: 0        Meta.ordering: SIN TOCAR

Tests M03-E2:         25 passed / 0 failed / 0 skipped
Regresión completa:  611 passed / 0 failed / 0 skipped   (586 base + 25)

Desempate:    dia → secuencia → id   -- verificado quitándolo
Producción:   SIN CAMBIOS (solo SELECT, read_only = True)
Commit:       no
```

**[DECISIÓN APROBADA]** `secuencia` sigue siendo **ORDEN PROPUESTO**. E2 no
decidió qué hacer con los duplicados, ni qué significa el `0`, ni si debe
recompactarse.

---

## 1. Estado actual medido

**[MEDIDO]** Producción, solo `SELECT`:

```
planes ........................ 0        líneas ......................... 0
distribución de secuencia ..... vacía    empates ........................ 0
órdenes con línea ............. 0        líneas por día ................. vacío
```

> **Sigue sin haber una sola línea de plan en producción.** Toda la medición de
> secuencias y empates de §7 y §8 da **0 sobre 0** — no porque no haya empates,
> sino porque **no hay nada que medir todavía**.
>
> Eso es, en sí, el argumento de E2: las decisiones E-1 y E-2 no tienen dato que
> las sostenga, y **no lo tendrán hasta que alguien programe algo y pueda verlo**.

---

## 2. Vía de lectura

**[MEDIDO]** Antes de crear nada se buscó algo reutilizable:

| Superficie | ¿Existe? |
|---|:--:|
| serializador de `ProgramacionOrden` | **no** |
| vista de `ProgramacionOrden` | **no** |
| endpoint de lectura del plan | **no** |
| `secuencia` en alguna respuesta | **no** |

**No había nada que reutilizar.** Los 6 serializadores y 7 vistas de
`operaciones/` son de propuestas, disponibilidad y publicación.

**[IMPLEMENTADO]**

```
GET /api/operaciones/programacion/jornada/?dia=YYYY-MM-DD
GET /api/operaciones/programacion/jornada/?plan=<uuid>
```

**[DISEÑO]** Sin filtro responde **400**: *"la jornada" no significa nada sin un
día o un plan*. Devolver todo el histórico por defecto habría sido un recurso
distinto del que el encargo pide.

---

## 3. Campos observables

**[IMPLEMENTADO]** `LineaJornadaSerializer` expone:

| Grupo | Campos |
|---|---|
| **planificación** | **`secuencia`**, **`zona`**, **`prioridad`** |
| la línea | `id`, `dia`, `hora_inicio`, `hora_fin`, `estado` |
| el plan | `programacion`, `plan_semana`, `plan_estado` |
| la orden, lo justo | `orden`, `numero`, `cliente`, `estado_orden`, `programada_para` |

### Qué se expone y qué no, y por qué

**[DISEÑO]** Los tres campos de planificación se exponen **porque ése es el
objeto de E2**: hasta ahora se podían escribir y no leer.

**`prioridad` se incluye aunque ningún consumidor la aplique** — M03-E1 midió que
no aparece en ningún `order_by`. Se expone **para que eso se vea**, no para
sugerir que ordena. Hay prueba de que el orden lo da `secuencia`.

**[DISEÑO] Lo que NO se expone:** `cliente_telefono`, `cliente_direccion`,
`gps_lat`, `gps_lng`, `datos`, `contexto`. Mirar un plan no requiere el teléfono
ni el GPS del domicilio. Hay prueba (`test_1b`) que lo verifica campo por campo.

---

## 4. Ordenamiento actual

**[MEDIDO]** Las cuatro consultas que ordenan `ProgramacionOrden`:

| # | Dónde | Antes | Ahora |
|:--:|---|---|---|
| 1 | `Meta.ordering` | `["dia","secuencia"]` | **SIN TOCAR** — ver abajo |
| 2 | `_lineas_vigentes` | `.order_by("dia","secuencia")` | **`+ "id"`** |
| 3 | `_ordenes_con_dos_lineas_vigentes` | `.order_by("dia","secuencia")` | **`+ "id"`** |
| 4 | `supervisor._programacion_vigente().first()` | hereda `Meta.ordering` | **SIN TOCAR** — es M09 |

### Por qué `Meta.ordering` no se tocó

**[MEDIDO]** Cambiar `Meta.ordering` **genera una migración de estado en
Django**, y §9 obliga a detenerse si `makemigrations --check` detecta algo. El
encargo además pedía preferir `order_by()` explícitos. Las dos razones apuntan al
mismo sitio.

**[RIESGO]** Consecuencia honesta: **la consulta nº 4 sigue sin desempate**, y es
de M09, que no se puede modificar.

> **No es un riesgo abierto en la práctica:** esa consulta filtra **por una sola
> orden**, y desde M03-D3.2 la invariante I-1 impide que una orden tenga dos
> líneas vigentes. Con una sola fila, `.first()` no tiene nada que desempatar.
>
> Queda anotado porque **si alguna vez I-1 se relajara, ese `.first()` volvería a
> ser arbitrario** — y nadie lo vería.

---

## 5. Ordenamiento determinista

**[IMPLEMENTADO]**

```python
ORDEN_JORNADA = ("dia", "secuencia", "id")
```

**[VALIDADO] Verificado quitándolo.** Con `ORDEN_JORNADA = ("dia","secuencia")`:

```
test_8_el_desempate_es_por_identificador_estable   →  FAILED
(restaurado)                                       →  25 passed
```

---

## 6. Definición técnica del desempate

**[DISEÑO]** Había tres candidatas entre los campos existentes, y **dos se
descartaron por decir demasiado**:

| Candidata | Por qué no / sí |
|---|---|
| `hora_inicio` | **descartada**: es `null=True`, y tiene lectura operativa —*"el que empieza antes va primero"*—. Elegirla sería **decidir una regla de orden**, y eso es E-1 |
| `created_at` | **descartada**: tiene lectura de política —*"el que se registró primero va primero"*—. Mismo problema |
| **`id`** | **elegida**: UUID4, único, `NOT NULL`, y **sin ningún significado** |

> **Se elige `id` precisamente porque no dice nada.** Dos líneas empatadas
> **están** empatadas: el sistema no tiene con qué ordenarlas, y fingir un
> criterio sería peor que mostrar un orden estable y **declarar el empate**.

**[IMPLEMENTADO]** Por eso el resumen incluye `orden_arbitrario: true` cuando
**todas** las líneas de un día comparten número: el lector se entera de que lo
que ve es estable pero no significa nada.

**[MEDIDO]** El desempate **no reordena lo que ya estaba ordenado**: con
secuencias 9 y 1, salen 1 y 9 (`test_9b`).

---

## 7. Medición de `secuencia = 0`

**[DECISIÓN APROBADA — no tomada aquí]** E-2 sigue pendiente. E2 **solo cuenta**.

**[MEDIDO]** Producción:

```
total de líneas ............. 0
secuencia = 0 ............... 0
secuencia > 0 ............... 0
distribución ................ vacía
líneas por día .............. vacío
líneas por plan ............. 0 planes
```

**[IMPLEMENTADO]** El endpoint devuelve la misma medición para cualquier
conjunto, por día y en total:

```jsonc
"resumen": {
  "lineas": 3, "secuencia_cero": 3, "secuencia_mayor_que_cero": 0,
  "lineas_en_empate": 3,
  "dias": [{ "dia": "2026-10-07", "lineas": 3,
             "secuencia_cero": 3, "secuencia_mayor_que_cero": 0,
             "secuencias_empatadas": [0], "lineas_en_empate": 3,
             "orden_arbitrario": true }],
  "desempate": "dia -> secuencia -> id",
  "nota": "..."
}
```

**[DISEÑO]** El resumen **no llama al `0` "sin ordenar" ni "primera"**. Hay una
prueba que lo verifica sobre el texto del resumen (`test_7`), y otra que
comprueba que no aparece ningún veredicto —`error`, `warning`, `invalido`— en
ninguna parte (`test_el_resumen_no_interpreta...`).

> Quien decida E-2 verá **números**, no una etiqueta que ya decide por él.

---

## 8. Medición de empates

**[MEDIDO]** Producción, las dos consultas que el encargo pide:

| Consulta | Resultado |
|---|:--:|
| empates de secuencia **mismo día, mismo plan** | **0** |
| empates **mismo día, cualquier plan** (por organización) | **0** |
| órdenes afectadas | **0** |

Sobre **0 líneas totales**.

**[IMPLEMENTADO]** En el endpoint, los empates se cuentan por día:
`secuencias_empatadas` (qué números empatan) y `lineas_en_empate` (cuántas filas
están afectadas).

**[DECISIÓN APROBADA — no tomada aquí]** **No se resuelven, no son ERROR, no son
WARNING.** Se cuentan. Hay prueba de que tras leer un día con dos líneas en `1`,
**las dos siguen valiendo 1** (`test_6`).

---

## 9. I-1

**[VALIDADO]** Sigue funcionando, sin cambios en su lógica:

| | |
|---|---|
| dos líneas vigentes en planes distintos → detectado | `test_13` |
| **un empate de secuencia NO es un problema de coherencia** | `test_13b` — `revisar_coherencia` devuelve `[]` |

**[DISEÑO]** `test_13b` es el que fija la frontera: E-5 sigue pendiente, así que
**E2 mide el empate y no lo convierte en error**.

**[IMPLEMENTADO]** El único cambio que tocó I-1 fue añadir `"id"` a su
`order_by` — que solo afecta el **orden en que lista las líneas del mensaje**, no
su detección.

---

## 10. Multi-tenant

**[VALIDADO]**

| Caso | Resultado |
|---|---|
| A lee el día: ve solo lo suyo | `count == 1`, su propia orden |
| B lee el mismo día: ve solo lo suyo | `count == 1`, la suya |
| A pide el plan de B | **404** — no 403: un 403 confirmaría que existe |

**[IMPLEMENTADO]** `lineas_de_jornada(org, ...)` filtra por `org` en la consulta;
la vista resuelve el plan acotado a `request.org`. **La organización sale de
`request.org`, nunca del cliente.**

---

## 11. Permisos

**[IMPLEMENTADO]** `permission_classes = [EsJefeDeOperaciones]` → `ROLES_GESTION`
= `{ADMIN, SUPERVISOR, OPERACIONES}`. **Reutilizado, 0 roles nuevos.**

**[VALIDADO]** Un `USER` recibe **403**; sin sesión, **403**.

---

## 12. Tests

**[VALIDADO]** Los 14 puntos del §8, más 11 propios:

| # | Punto del encargo | Prueba | |
|:--:|---|---|:--:|
| 1 | lectura de jornada | `test_1`, `1b`, `1c`, `1d` | **PASS** |
| 2 | aislamiento multi-tenant | `test_2`, `2b` | **PASS** |
| 3 | permisos | `test_3`, `3b` | **PASS** |
| 4 | día con secuencias diferentes | `test_4` | **PASS** |
| 5 | **día con todas las secuencias 0** | `test_5` | **PASS** |
| 6 | secuencias duplicadas | `test_6` | **PASS** |
| 7 | secuencias 0 y >0 | `test_7` | **PASS** |
| 8 | **desempate determinista** | `test_8` *(verificado quitándolo)* | **PASS** |
| 9 | misma consulta, mismo orden | `test_9` *(ver abajo)* | **PASS** |
| 10 | plan borrador | `test_10` | **PASS** |
| 11 | plan publicado | `test_11` | **PASS** |
| 12 | `REPROGRAMADA` no se confunde con vigente | `test_12` | **PASS** |
| 13 | I-1 sigue detectándose | `test_13`, `13b` | **PASS** |
| 14 | las 4 rutas de D3 se leen | `test_14` | **PASS** |
| — | **leer no cambia nada** | `test_1e` | **PASS** |
| — | no expone datos del cliente | `test_1b` | **PASS** |
| — | el desempate no reordena lo ya ordenado | `test_9b` | **PASS** |
| — | el resumen no interpreta ni juzga | `test_el_resumen...` | **PASS** |
| — | E2 no toca M09 | `test_e2_no_toca_m09` | **PASS** |
| — | 0 conexiones salientes | `test_ninguna_conexion...` | **PASS** |

```
25 passed · 0 failed · 0 skipped
```

### Una prueba mía que resultó más débil de lo que parecía

**[MEDIDO]** Al quitar el desempate para comprobar que `test_8` lo mide,
**`test_9` siguió pasando**.

> Con cinco filas, PostgreSQL devuelve un orden estable **por casualidad** —un
> recorrido secuencial— y la falta de tercera clave no se nota.

**[DISEÑO]** No se puede escribir una prueba que falle de forma fiable ante algo
que por definición es no determinista. Así que se hizo lo honesto: **el docstring
de `test_9` ahora dice que es un control de humo y que la garantía la da
`test_8`** — el que afirma que el orden **es** por `id`.

Sin esa aclaración, `test_9` habría quedado como "prueba de determinismo", que es
justo lo que no es.

---

## 13. Regresión

```
pytest operaciones/tests/ campo/tests/
  611 passed, 0 failed, 0 skipped      en 249s
```

| | |
|---|---|
| Baseline (M03-D3.2) | **586** |
| M03-E2 | **+25** |
| **Total** | **611** |

**[VALIDADO]** Ninguna regresión. Las suites de M03-B (29), M03-C (30),
M03-D3 (33) y M03-D3.2 (17) pasan sin cambios.

### La guarda de M09-F, actualizada con su motivo

`test_no_existe_ninguna_ruta_de_ejecucion` fija el inventario exacto de rutas de
`operaciones`, y `programacion-jornada` la hizo fallar. Es la guarda funcionando.

**Qué se hizo:** actualizar el conjunto **y escribir por qué esta ruta no es de
ejecución** — *es un **GET**: no escribe ni una fila, no reordena, no recompacta
y no resuelve ningún empate*. La comprobación sustantiva (ningún nombre contiene
`ejecutar`, `aplicar`, `despachar`) sigue intacta, y el conjunto sigue siendo
exacto.

---

## 14. Producción

# SIN CAMBIOS

**[MEDIDO]** Solo `SELECT`, `read_only = True`:

```
django_migrations 192 · tablas public 135 · índices public 829
planes 0 · líneas 0 · PropuestaSupervisor 0 · acciones_propuestas 40
operaciones_externas 0 · kill switch detenido
```

**[VALIDADO] 0 efectos externos** (§10): instrumentado en `socket.connect`, y el
cero se leyó **después de probar que el instrumento dispara** con una sonda
deliberada.

Todo se implementó y probó en un contenedor PostgreSQL 16 aislado (`pg-e2`), con
un runner sin una sola credencial de producción. Entorno eliminado al terminar.

---

## 15. Archivos y GAPs

### Creado (1)

`operaciones/tests/test_m03e2_jornada.py` — 25 pruebas.

### Modificados (5)

| Archivo | Cambio |
|---|---|
| `operaciones/programacion.py` | `ORDEN_JORNADA`, `lineas_de_jornada`, `resumen_de_jornada`; `+ "id"` en los 2 `order_by` explícitos |
| `operaciones/serializers.py` | `+1 LineaJornadaSerializer` |
| `operaciones/views.py` | `+1 JornadaView` |
| `operaciones/urls.py` | `+1 ruta` |
| `operaciones/tests/test_m09f_gobernanza.py` | guarda de rutas + el motivo |

**0 modelos, 0 migraciones, 0 roles, `Meta.ordering` sin tocar, M09 sin tocar.**

### GAPs

| # | GAP | Tipo | ¿Bloquea? |
|:--:|---|---|:--:|
| **E-1** | **¿qué hacer con un duplicado?** | **[PENDIENTE]** decisión | **E3** |
| **E-2** | **¿qué significa `secuencia = 0`?** | **[PENDIENTE]** decisión | **E3** |
| **E-4** | ¿publicar hace algo con las secuencias? | [PENDIENTE] | E3 |
| **E-5** | ¿duplicidad en `revisar_coherencia`: ERROR/WARNING/nada? | [PENDIENTE] | E3 |
| E-6 | ¿`prioridad` debe ordenar? Sigue expuesta y sin usar | [PENDIENTE] | — |
| E-7 | ¿`zona` debe agrupar? Texto libre sin catálogo | [PENDIENTE] | M03-F |
| **R-1** | **`_programacion_vigente` de M09 sigue sin desempate** (no se puede tocar) | **[RIESGO]** | no |
| R-2 | **Sin datos**: 0 planes, 0 líneas. E-1 y E-2 siguen sin evidencia empírica | **[RIESGO]** | no |
| R-3 | La jornada no tiene pantalla: la vía es API | [PENDIENTE] producto | no |

---

## 16. Alcance exacto de E3

**[DISEÑO]** E2 entrega lo que E3 necesitaba para poder decidir:

| | E3 ahora puede | Porque |
|---|---|---|
| **1** | **ver** el efecto de cualquier regla que implemente | la jornada es legible |
| **2** | **medir** empates antes y después | el resumen los cuenta |
| **3** | confiar en que el orden es reproducible | el desempate está y está probado |

**[PENDIENTE] Lo que E3 no puede hacer sin firma:**

```
recompactar ................... E-1
reasignar al mover ............ E-1   (y chocaría con M03-D3.2)
validar al publicar ........... E-4, E-5
ERROR/WARNING por duplicado ... E-5
prioridad en el orden ......... E-6
```

**[RIESGO] Y el dato que más pesa sobre el orden de la cola:** **0 planes y 0
líneas en producción**, y las 3 órdenes reales clasifican como **contingencia**.

> La medición que E-1 y E-2 necesitan **no existe todavía**, y E2 no la puede
> fabricar: hace falta que alguien programe trabajo de verdad. **Decidir E-1 hoy
> sería decidir sobre un fenómeno que nadie ha observado.**

---

```
código ......... 1 archivo de pruebas + 5 modificados
migraciones .... 0     modelos .... 0     roles .... 0     M09 .... sin tocar
producción ..... SIN CAMBIOS (solo SELECT, read_only = True)
commit ......... no
```
