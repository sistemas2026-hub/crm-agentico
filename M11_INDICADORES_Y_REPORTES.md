# M11 — Indicadores y reportes operativos

**Fecha:** 2026-09-19
**Veredicto:** **M11 = GO**

---

## 1. GO / NO-GO

# GO

| # | Criterio (§P) | |
|:--:|---|:--:|
| 1 | Indicadores principales funcionan | **SÍ** — 6 bloques |
| 2 | Reportes funcionan | **SÍ** — 5 |
| 3 | Dashboard reutiliza infraestructura existente | **SÍ** — se envuelve `cases/analytics.py`, no se reescribe |
| 4 | Datos insuficientes son explícitos | **SÍ** — 3 estados, cobertura y motivo en cada indicador |
| 5 | Capacidad respeta M03-G | **SÍ** — se llama, no se recalcula |
| 6 | SLA no inventa reglas | **SÍ** — solo campos y propiedades que `Case` ya define |
| 7 | Supervisor visible sin crear otra cola | **SÍ** |
| 8 | Tenant isolation | **SÍ** |
| 9 | Sin modificaciones de producción | **SÍ** |
| 10 | Pruebas propias pasan | **SÍ** — 20/20 |
| 11 | M02 / M03 / M09 siguen pasando | **SÍ** |
| 12 | Regresión global ejecutada | **SÍ** — 4437 passed |

```
Pruebas propias ....  20 passed / 0 failed / 0 skipped
Regresion ..........  4437 passed / 1 failed / 19 skipped
Migraciones ........  0    Modelos: 0    Tablas de KPI: 0    Colas nuevas: 0
Rutas nuevas .......  2 (ambas GET)      Frontend modificado: 0
Efectos externos ...  0    Produccion: SIN CAMBIOS
Commit .............  no
```

---

## 2. Archivos modificados

| Archivo | Cambio |
|---|---|
| `operaciones/indicadores.py` | **CREADO** — 621 líneas |
| `operaciones/tests/test_m11_indicadores.py` | **CREADO** — 595 líneas, 20 pruebas |
| `operaciones/views.py` | +2 vistas GET |
| `operaciones/serializers.py` | +1 `ReporteSerializer` |
| `operaciones/urls.py` | +2 rutas |
| `operaciones/tests/test_m09f_gobernanza.py` | +2 rutas declaradas con su justificación |

**Sin tocar:** `cases/` (verificado) · `supervisor.py` · `capacidad.py` ·
`actividades.py` · `programacion.py` · `models.py` · `habilidades.py` ·
frontend · kill switch · B-7 · M02 · M03 · M09.

---

## 3. Modelos

# 0 creados · 0 modificados

Verificado leyendo la app real. **No hay tabla de KPI, no hay tabla de hechos,
no hay data warehouse.** Cada número se deriva de la fila que lo sostiene, en
el momento de la consulta — un número guardado queda viejo en cuanto cambia esa
fila.

---

## 4. Migraciones

```
makemigrations --check  ->  "No changes detected"
```

# 0

---

## 5. Rutas

```
GET /api/operaciones/indicadores/?desde=&hasta=&dias=
GET /api/operaciones/reportes/?reporte=diario|pendientes|programacion|compromisos|supervisor
```

**Dos, ambas GET**, declaradas en el guarda de gobernanza con su justificación.
El nombre del reporte va como parámetro de **consulta**, no en la ruta: un
`<str:>` en el path habría necesitado una excepción en el guarda de rutas
malformadas — la misma lección de M09-M.

---

## 6. Componentes frontend

# 0 modificados

**No existe pantalla de operaciones que extender.** El barrido de
`frontend/src/routes/(app)/` no encontró ninguna ruta de reportes, indicadores
ni operaciones. §G dice *"si existe dashboard reutilizable, extenderlo"* y
*"NO construir otro frontend paralelo"* — construir uno desde cero habría sido
exactamente lo segundo.

**La API queda lista para consumo**, con la forma documentada abajo.

El único archivo de frontend modificado en el repo
(`conversaciones/[id]/+page.svelte`) **es anterior a esta sesión**.

---

## 7. Indicadores implementados

### 7.1 Casos (§B.1) — se **envuelve** lo que ya existía

`cases/analytics.py` ya computaba FRT, MTTR, backlog, agentes y SLA, con su
dashboard. **M11 no lo reescribe: lo llama y le agrega el sobre de cobertura
que le falta.**

`compute_frt` promedia sobre los casos que **tienen** `first_response_at` y
devuelve cuántos son. El cálculo está bien; lo que faltaba era decir **sobre
cuántos se calculó**. Eso se agrega sin tocar ese módulo — reescribir el
promedio habría creado una segunda verdad sobre el mismo número.

| | |
|---|---|
| Conteos | total · en periodo · abiertos · cerrados · por estado · por prioridad · por tipo |
| Derivadas envueltas | `primera_respuesta_horas` · `resolucion_horas` |

### 7.2 Actividades (§B.2)

total · abiertas · vencidas · sin responsable · con dependencia pendiente ·
validación pendiente · **los 7 estados operativos** · **los 9 tipos**.

**El catálogo entero, incluidos los que están en cero.** Un tipo que no aparece
se lee como *"no existe"*, y no es lo mismo que *"hay cero"*.

### 7.3 Programación y capacidad (§B.3)

órdenes total / abiertas / programadas / sin programar · líneas vigentes ·
planes publicados y en borrador · asignaciones · órdenes sin cuadrilla ·
**órdenes con gente pero sin principal** · novedades.

**La capacidad la da M03-G**, con su regla intacta: la sobrecarga solo se
cuenta donde la carga **conocida** ya no cabe; donde faltan duraciones el día
va a `jornadas_no_determinables`, **no a cero**.

### 7.4 Compromisos (§B.4)

total · abiertos · vencidos · por vencer · a tiempo · **sin fecha** ·
bloqueados · en espera · validación pendiente.

**"Sin fecha" se cuenta aparte**: un compromiso sin fecha es legítimo (M02) y
**no es lo mismo que "a tiempo"**. La ventana de "por vencer" es explícita y
por defecto la que ya usa el detector de M09 — no un valor nuevo.

### 7.5 Supervisor IA (§B.5)

señales vigentes y por tipo · propuestas total y en periodo · **los 6 estados**
· **los 10 tipos de señal** · tasa de revisión.

Las señales se detectan **sin escribir**: consultar el indicador **no corre el
ciclo ni crea propuestas**.

### 7.6 SLA (§D)

dentro de SLA · vencidos · **pausados** · **no calculable** · cumplimiento.

Todo sale de campos y propiedades que `Case` **ya define** — que respetan el
calendario laboral y la semántica de pausa. **No se inventó ningún tiempo
objetivo, prioridad, calendario, pausa ni regla.** Un caso sin objetivo
declarado se cuenta como **no calculable**, no como cumplido.

---

## 8. Indicadores NO implementados, y por qué

| Indicador | Por qué no |
|---|---|
| **Productividad / eficiencia** | No existe definición formal (§E lo prohíbe). Una métrica de "eficiencia" sin regla sería inventada |
| **Desplazamiento** | Hay GPS, no hay regla distancia→minutos, y los servicios externos están prohibidos |
| **Complejidad** | No existe ninguna estructura |
| **Tendencias / series temporales propias** | `cases/analytics.py` ya las produce para casos. Para operaciones haría falta historizar, y eso exige una tabla de hechos — prohibido por §A |
| **Umbrales / semáforos** | §G y §O prohíben inventarlos, y no hay ninguno configurado oficialmente |

---

## 9. Cobertura de datos

**Tres estados, y el tercero no es decoración:**

```
VALIDO               el numero representa lo que dice representar
DATOS_INSUFICIENTES  hay un valor, pero NO sobre toda la poblacion
NO_APLICA            no hay poblacion sobre la cual calcular
```

### Por qué no hay umbral de cobertura

Sería un número inventado, y está prohibido. **La regla no necesita uno:**

- un **conteo** sobre un campo obligatorio es siempre `VALIDO` — no hay nada
  que pueda faltar;
- una **derivada** (promedio, proporción) sobre un campo opcional es
  `DATOS_INSUFICIENTES` **en cuanto la cobertura baja del 100%**, porque cada
  valor ausente desplaza el resultado en una dirección que nadie puede saber.

**El valor igual se devuelve, etiquetado.** Ocultarlo sería otra forma de
perder información; presentarlo limpio sería mentir. Con su cobertura al lado
dice lo que es.

**Y 0 población no es 0%: es `NO_APLICA`.** Un *"0% de incumplimiento"* sobre
cero casos parece un logro y no significa nada.

Cada indicador trae: `estado`, `valor`, `unidad`, `denominador`, `con_dato`,
`cobertura`, `periodo`, `fuente` y `motivo`.

**No se imputa, no se rellena, no se supone.**

---

## 10. Reportes

Los cinco de §F: **diario · pendientes · programacion · compromisos ·
supervisor**.

Cada uno trae periodo, fecha de generación, filtros, **fuentes**, métricas,
`cobertura_completa`, **la lista de todo lo que no se pudo calcular** (recorrida
del árbol de métricas, para que el lector no tenga que inspeccionar indicador
por indicador) y **observaciones**.

Las observaciones dicen lo que los números **no** demuestran:

> *"'vencida' significa que la fecha objetivo pasó y la actividad no está
> cerrada. NO significa que alguien haya incumplido: la causa no está
> registrada."*

> *"La capacidad se deriva; no hay ningún porcentaje guardado. Donde faltan
> duraciones el resultado es INDETERMINADO, que no es cero."*

> *"'acciones_propuestas' (histórico del motor) NO se mezcla acá: es otra
> semántica y otra tabla."*

**Ninguna conclusión causal.** Los reportes no se guardan ni se historizan, y
lo dicen.

---

## 11. Dashboard

**Se reutiliza el que existe.** `cases/analytics.py` + `analytics_views.py`
(1135 líneas, rutas `analytics/frt/`, `analytics/mttr/`, `analytics/backlog/`…)
quedaron **intactos**; M11 los consume.

Para operaciones no había dashboard y **no se construyó un frontend paralelo**
(§G). La API entrega en una sola llamada volumen, pendientes, vencidos,
bloqueados, programación, capacidad, propuestas del Supervisor y **datos
incompletos** — que es lo que §G pide poder identificar rápido.

---

## 12. Seguridad

| Verificación | Resultado |
|---|---|
| Cada organización ve solo lo suyo | **sí** — medido con dos tenants poblados distinto |
| Ningún agregado cruza tenants | **sí** — todo filtra por `org` en la consulta |
| Técnico consulta indicadores | **403** |
| Técnico consulta reportes | **403** |
| Permisos nuevos | **0** — se reutiliza `EsJefeDeOperaciones` |

`operaciones_*` tiene RLS forzada; `campo_*` no — ahí el aislamiento es
aplicativo, y M11 no lo cambia ni pretende hacerlo.

---

## 13. Rendimiento

**[MEDIDO]** Se revisaron los índices existentes antes de escribir:
`ActividadOperativa` tiene 3 índices compuestos —`(org, estado_operativo,
vence_en)`, `(org, responsable, estado_operativo)`, `(org, origen_tipo,
origen_id)`— que cubren exactamente los filtros de estos indicadores.
`PropuestaSupervisor` tiene `idx_propuesta_dedup`.

**Decisiones tomadas:**

- Los conteos se resuelven con `values().annotate(Count)` — **una consulta por
  agrupación**, no una por fila.
- `con_dependencia_pendiente` usa `select_related("depende_de")` y
  `only(...)` para evitar N+1 al leer la propiedad.
- `ordenes_sin_principal` usa `prefetch_related("asignaciones")`.
- **Sin caché persistente.** Un KPI cacheado queda viejo, y §K dice no
  introducirla si no es necesaria.

**[DEUDA] Lo que sí crece:** `indicadores_programacion` llama a
`capacidad_de_jornada` **una vez por día con trabajo** dentro del horizonte
(7 por defecto), y cada llamada recorre las líneas de ese día. Con volumen alto
hará falta acotar el horizonte o agrupar la consulta. Queda documentado, no
optimizado prematuramente: producción tiene 0 líneas programadas.

---

## 14. Pruebas propias

```
20 passed / 0 failed / 0 skipped
```

Las 20 de §M. **Lo que más se prueba no son los conteos —que son fáciles— sino
las tres formas de mentir sin querer:**

| Prueba | Qué demuestra |
|---|---|
| `test_11_12` | Cobertura parcial **de verdad** (1 de 3 casos con `first_response_at`): el promedio **no** se presenta como válido, pero **tampoco se oculta** |
| `test_11b` | 0 sobre 0 es `NO_APLICA`, **no 0%** |
| `test_13` | Un caso sin objetivo de SLA se cuenta **no calculable**, no cumplido |
| `test_9` | Sin calendario, la capacidad **no** se reporta como cero |
| `test_18` | Generar los 5 reportes **no crea ni cambia nada** — medido sobre 6 conjuntos de entidades, **sin usar el contador de `Activity` como prueba** |
| `test_19` | Sin segunda cola ni tabla de KPI, y sin **ninguna** escritura — verificado sobre el **AST** |
| `test_2_3_4` | El catálogo entero de tipos, incluidos los que están en cero |

**Dos correcciones a mis propias expectativas**, ambas por medir en vez de
suponer:

1. `sin_responsable` daba 3 y yo esperaba 4: una actividad **completada** sin
   responsable ya no es una señal, y el indicador la excluye correctamente.
2. `tasa_revision` daba `None`: consulté con un `ahora` capturado **antes** de
   correr el ciclo, y la ventana es `[desde, hasta)` — las propuestas se
   crearon después. El indicador estaba bien; la prueba preguntaba mal.

---

## 15. Regresión completa

```
4437 passed · 1 failed · 19 skipped        (19m 29s)
```

| Cat. | Fallo | |
|:--:|---|---|
| **FAIL REAL (por M11)** | — | **0** |
| **FAIL PREEXISTENTE** | — | 0 |
| **BLOCKED POR ENTORNO** | `test_portal_rls` | **1** |

**Cero fallos atribuibles.** Las dos rutas se declararon en el guarda de
gobernanza **antes** de correr la regresión, y el nombre del reporte se puso en
la query en vez de en el path — las dos lecciones de M09-M, aplicadas por
adelantado.

`test_portal_rls`: `postgres_only`, exige rol no-superusuario y
`crm.test_settings_postgres`; bajo esa configuración da 2 passed (probado en
M03-F-B, M03-G y M02).

---

## 16. Producción

# SIN CAMBIOS

Solo `SELECT`, `read_only = True`. **20 claves específicas → DIFERENCIAS:
NINGUNA.**

**Se usaron fuentes específicas, no el contador de `Activity`** — §N lo pide
explícitamente y M09-L ya había mostrado por qué: esa tabla es viva y sube sola
con el CRM real.

```
django_migrations 192 · ledger 50 · tablas public 135 · indices public 829
ActividadOperativa 0 · PropuestaSupervisor 0 · acciones_propuestas 40
activity WHERE entity_type IN (ActividadOperativa, PropuestaSupervisor) = 0
OrdenTrabajo 3 · AsignacionTrabajo 3 · EventoTrabajo 12 · Profile 5
ProgramacionSemanal 0 · ProgramacionOrden 0 · NovedadOperativa 0
teams 0 · Disponibilidad 0 · operaciones_externas 0 · MutacionIdempotente 14
BusinessCalendar 1 · kill switch detenido
```

Ni `migrate`, ni `seed`, ni `INSERT`/`UPDATE`/`DELETE`/`ALTER`, ni integraciones
externas. Todo en contenedores aislados **sin una sola credencial de
producción**.

---

## 17. Deuda técnica

| # | Deuda |
|:--:|---|
| 1 | **Sin frontend de operaciones** — la API está lista; la pantalla es una decisión aparte |
| 2 | **`indicadores_programacion` llama a capacidad día por día** — acotar con volumen (§13) |
| 3 | **Sin historización**: los reportes son del momento. Tendencias propias exigirían una tabla de hechos, hoy prohibida |
| 4 | **`cases/analytics.py` no declara cobertura por sí mismo** — M11 la agrega desde fuera; consolidarlo allá sería una mejora de ese módulo |
| 5 | **Duración por tipo de trabajo sin declarar** en producción: toda jornada real dará no-determinable |
| 6 | **Sin umbrales oficiales** — no hay semáforos porque no hay umbral configurado que reutilizar |
| 7 | RLS de `campo_*` · B-7 · H-05 bloqueada · zona · vehículo · autonomía 2+ |

---

## 18. Decisiones pendientes

Ninguna bloqueó este paso. Las abiertas vienen de antes:

1. **¿Se desbloquea H-05?** (M09-L / M09-M).
2. **¿Se declara la duración por tipo de trabajo?** Sin ella, la capacidad real
   siempre será parcial — y M11 lo dirá, en vez de inventarla.
3. **¿Se construye la pantalla de operaciones?** Depende de si se extiende el
   dashboard de casos o se hace una vista propia.
4. **¿Se definen umbrales oficiales?** Sin ellos no hay semáforos, y M11 no los
   inventa.

---

## 19. Conclusión ejecutiva

M11 es una capa de **lectura y cálculo**, y nada más: cero modelos, cero
migraciones, cero tablas de hechos, cero colas, cero frontend paralelo. Dos
rutas GET y un módulo que **agrega** sobre lo que ya calculaban `cases`, M02,
M03-G y M09 — sin recalcular ninguno, porque duplicar un cálculo crea una
segunda verdad sobre el mismo número.

Lo que aporta de nuevo no son los conteos, que eran fáciles. Es **el sobre de
honestidad**: cada indicador dice sobre cuánta población se calculó, y los tres
estados separan *"esto es cierto"* de *"esto es cierto sobre una parte"* de
*"no hay nada que calcular"*. Sin umbral inventado: un conteo sobre campo
obligatorio siempre vale; una derivada sobre campo opcional deja de valer en
cuanto falta un dato.

Y los reportes dicen lo que los números **no** prueban. Que una actividad esté
vencida no significa que alguien haya incumplido — la causa no está registrada,
y el reporte lo dice en vez de dejar que el lector lo suponga.

Cero fallos atribuibles en la regresión: las dos lecciones de M09-M —declarar
la ruta en gobernanza, y no meter parámetros en el path— se aplicaron antes de
correr, no después de romper.

```
codigo ......... 1 archivo creado (621) · 4 modificados
pruebas ........ 1 archivo creado (20 pruebas, 595 lineas)
migraciones .... 0   modelos ... 0   tablas KPI ... 0   colas ... 0   frontend ... 0
cases/ · M02 · M03 · M09 · habilidades · kill switch · B-7 ...... sin tocar
produccion ..... SIN CAMBIOS (solo SELECT, read_only = True)
entorno aislado  eliminado
commit ......... no    despliegue ... no    M10/B-7/autonomia ... no
```
